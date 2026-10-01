"""Pick an image or video model from the prompt and each model's note."""

from __future__ import annotations

import re

from holix_media.config import MediaProvider

_EDIT = re.compile(
    r"("
    r"измени|поменя|замени|добав|убер|удали|поправ|дорису|перерису|"
    r"ожив|анимир|взаимодейств|"
    r"\bedit\b|\bchange\b|\brestyle\b|\binpaint\b|\banimate\b|"
    r"\bremove\b|\breplace\b|\badd\b"
    r")",
    re.IGNORECASE,
)
_EXISTING = re.compile(
    r"(изображен|картин|фото|кадр|видео|ролик|"
    r"\bimage\b|\bpicture\b|\bphoto\b|\bframe\b|\bvideo\b|\bclip\b)",
    re.IGNORECASE,
)
_TEXT_ONLY_NOTE = (
    "без референс",
    "только текст",
    "text-to-image",
    "text to image",
    "text-to-video",
    "text to video",
    "без изображен",
)
_REFERENCE_NOTE = (
    "референс",
    "reference",
    "input_image",
    "правк",
    "image-to-video",
    "image to video",
    "по фото",
    "по изображен",
    "i2v",
)


def request_needs_reference(prompt: str, *, has_references: bool) -> bool:
    """True when the user wants a model that can take an existing image."""
    if has_references:
        return True
    text = prompt or ""
    return bool(_EDIT.search(text) and _EXISTING.search(text))


def reference_capability(provider: MediaProvider) -> bool | None:
    """True accepts a reference, False is text-only, None is not labeled."""
    if provider.accepts_reference is not None:
        return provider.accepts_reference
    note = (provider.note or "").lower()
    if not note:
        return None
    if any(part in note for part in _TEXT_ONLY_NOTE):
        return False
    if any(part in note for part in _REFERENCE_NOTE):
        return True
    return None


def format_provider_menu(providers: tuple[MediaProvider, ...] | list[MediaProvider]) -> str:
    if not providers:
        return "(none)"
    lines: list[str] = []
    for provider in providers:
        flag = reference_capability(provider)
        if flag is True:
            kind = "accepts a reference image"
        elif flag is False:
            kind = "text prompt only"
        else:
            kind = "not labeled"
        note = provider.note.strip() or "(no note)"
        lines.append(f"- {provider.id} model={provider.model or provider.type}: {note} ({kind})")
    return "\n".join(lines)


def choose_provider(
    providers: tuple[MediaProvider, ...] | list[MediaProvider],
    *,
    prompt: str,
    has_references: bool,
    provider_id: str = "",
) -> tuple[MediaProvider | None, str]:
    """Return the model for this prompt, or an error the agent should show."""
    pool = [item for item in providers if item.model or item.base_url]
    if not pool:
        return None, ""
    needs_reference = request_needs_reference(prompt, has_references=has_references)
    menu = format_provider_menu(pool)
    if needs_reference and not has_references:
        return None, (
            "This prompt edits or interacts with an existing image or video. "
            "Pass that file in references. Do not use a text-only model.\n"
            f"Configured models:\n{menu}"
        )
    explicit = (provider_id or "").strip().lower()
    if explicit:
        named = next((item for item in pool if item.id.lower() == explicit), None)
        if named is not None and _compatible(named, needs_reference=needs_reference, pool=pool):
            return named, ""
    chosen = _match(pool, needs_reference=needs_reference)
    if chosen is not None:
        return chosen, ""
    if needs_reference:
        return None, (
            "This prompt needs a model that accepts a reference image. "
            "None of the configured models is marked that way. "
            "Set accepts_reference and a note in holix-media settings.\n"
            f"Configured models:\n{menu}"
        )
    return pool[0], ""


def _compatible(
    provider: MediaProvider, *, needs_reference: bool, pool: list[MediaProvider]
) -> bool:
    flag = reference_capability(provider)
    if needs_reference:
        return flag is not False
    if flag is not True:
        return True
    return not any(reference_capability(item) is not True for item in pool)


def _match(pool: list[MediaProvider], *, needs_reference: bool) -> MediaProvider | None:
    flags = [(item, reference_capability(item)) for item in pool]
    if needs_reference:
        for item, flag in flags:
            if flag is True:
                return item
        for item, flag in flags:
            if flag is None:
                return item
        return None
    for item, flag in flags:
        if flag is False:
            return item
    for item, flag in flags:
        if flag is None:
            return item
    return None
