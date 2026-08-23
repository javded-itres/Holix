"""Shared formatting for forwarded Telegram / MAX messages."""

from __future__ import annotations


def format_forward_header(origin: str, *, locale: str = "ru") -> str:
    from core.i18n.messages import t

    name = (origin or "").strip()
    if name:
        return t("msg.forward.from", locale, origin=name)
    return t("msg.forward.anon", locale)


def default_forward_instruction(locale: str = "ru") -> str:
    from core.i18n.messages import t

    return t("msg.forward.instruction", locale)


def combine_forward_text(
    *,
    forwarded: str = "",
    comment: str = "",
    origin: str = "",
    locale: str = "ru",
    has_media: bool = False,
) -> str:
    """Build the user-turn text the agent should see for a forwarded message."""
    from core.i18n.messages import t

    header = format_forward_header(origin, locale=locale)
    fwd = (forwarded or "").strip()
    note = (comment or "").strip()
    parts = [header]
    if fwd:
        parts.append(fwd)
    if note and note != fwd:
        parts.append(t("msg.forward.comment", locale, text=note))
    body = "\n\n".join(p for p in parts if p)
    if fwd or note:
        return body
    if has_media:
        return f"{body}\n\n{default_forward_instruction(locale)}"
    return f"{body}\n\n{default_forward_instruction(locale)}"
